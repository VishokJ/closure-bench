// A stalled word 8'h3C is accepted mid-frame (bit_cnt 2..9, busy high);
// that frame then delivers 8'hA5 with no overrun.
module cov_P15 (
  input logic       clk,
  input logic       rst,
  input logic [7:0] m_axis_tdata,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic       busy,
  input logic       overrun_error,
  input logic [3:0] bit_cnt
);

  // 0: idle; 1: 8'h3C stalled; 2: accepted mid-frame, waiting for delivery
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
            if (busy && bit_cnt >= 4'd2 && bit_cnt <= 4'd9) st <= 2'd2;
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

  P15_rx_accept_during_next_frame: cover property (@(posedge clk) disable iff (rst)
    st == 2'd2 && m_axis_tvalid && !$past(m_axis_tvalid) && busy &&
    m_axis_tdata == 8'hA5 && !overrun_error);

endmodule

bind uart_rx cov_P15 u_cov_P15 (.*);
