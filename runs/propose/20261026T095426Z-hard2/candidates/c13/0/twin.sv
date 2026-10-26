// Twin: the idle run after the frame error lasts exactly 15 clocks (one short
// of the target), then the next frame delivers 8'hA5.
module cov_P13_twin (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       busy,
  input logic       rxd,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata
);

  reg [1:0] st;
  reg [4:0] cnt;

  always @(posedge clk) begin
    if (rst) begin
      st  <= 2'd0;
      cnt <= 5'd0;
    end else begin
      if (frame_error) begin
        st  <= 2'd1;
        cnt <= 5'd0;
      end else if (st == 2'd1) begin
        if (!busy && rxd) begin
          if (cnt != 5'd31) cnt <= cnt + 5'd1;
        end else if (cnt != 5'd0) begin
          if (cnt >= 5'd16) st <= 2'd2;
          else if (cnt == 5'd15) st <= 2'd3;
          else st <= 2'd0;
          cnt <= 5'd0;
        end
      end
    end
  end

  P13_twin_idle_one_short: cover property (@(posedge clk) disable iff (rst)
    st == 2'd3 && !frame_error && $rose(m_axis_tvalid) && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_P13_twin u_cov_P13_twin (.*);
