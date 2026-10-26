// Twin: the stalled 8'h3C is accepted one step early, while bit_cnt is still
// 10 (start-bit phase) of the next frame; that frame then delivers 8'hA5.
module cov_P15_twin (
  input logic       clk,
  input logic       rst,
  input logic [7:0] m_axis_tdata,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic       busy,
  input logic       overrun_error,
  input logic [3:0] bit_cnt
);

  reg [1:0] st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 2'd0;
    end else begin
      case (st)
        2'd0: begin
          if (m_axis_tvalid && !m_axis_tready && m_axis_tdata == 8'h3C) st <= 2'd1;
        end
        2'd1: begin
          if (!m_axis_tvalid || m_axis_tdata != 8'h3C) begin
            st <= 2'd0;
          end else if (m_axis_tready) begin
            if (busy && bit_cnt == 4'd10) st <= 2'd2;
            else st <= 2'd0;
          end
        end
        2'd2: begin
          if (!busy || m_axis_tvalid) st <= 2'd0;
        end
        default: st <= 2'd0;
      endcase
    end
  end

  P15_twin_rx_accept_in_start_bit: cover property (@(posedge clk) disable iff (rst)
    st == 2'd2 && m_axis_tvalid && !$past(m_axis_tvalid) && busy &&
    m_axis_tdata == 8'hA5 && !overrun_error);

endmodule

bind uart_rx cov_P15_twin u_cov_P15_twin (.*);
