// Twin: tvalid rises one clock later, on the first idle clock where
// s_axis_tready is already high after the 8'hC3 frame's stop period.
module cov_P20_twin (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        txd,
  input logic        s_axis_tvalid,
  input logic        s_axis_tready
);

  reg       tvalid_q;
  reg [7:0] shift;
  reg       have;
  reg       prev_end;
  reg       hit;

  always @(posedge clk) begin
    if (rst) begin
      tvalid_q <= 1'b0;
      shift    <= 8'h00;
      have     <= 1'b0;
      prev_end <= 1'b0;
      hit      <= 1'b0;
    end else begin
      tvalid_q <= s_axis_tvalid;
      hit      <= 1'b0;
      prev_end <= (prescale_reg == 19'd0 && bit_cnt == 4'd0 && !s_axis_tready && !s_axis_tvalid);
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0) begin
        if (prev_end && s_axis_tvalid && !tvalid_q && s_axis_tready && have && shift == 8'hC3) begin
          hit <= 1'b1;
        end
        if (s_axis_tvalid) begin
          have  <= 1'b0;
          shift <= 8'h00;
        end
      end else if (prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
        shift <= {txd, shift[7:1]};
        if (bit_cnt == 4'd1) begin
          have <= 1'b1;
        end
      end
    end
  end

  P20_twin_tvalid_rise_one_late: cover property (@(posedge clk) disable iff (rst)
    hit && !txd && !s_axis_tready);

endmodule

bind uart_tx cov_P20_twin u_cov_P20_twin (.*);
